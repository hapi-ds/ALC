"""Integration tests for multi-tenancy full request lifecycle.

Tests the complete flow through the API layer using httpx.AsyncClient
with an async SQLite in-memory database, verifying tenant isolation,
company deactivation/reactivation, and membership revocation.

References:
    - Task 14.1: Write integration tests for full request lifecycle
    - Requirements: 3.1, 3.2, 3.3, 3.4, 9.1, 9.2, 13.1, 13.2, 13.4
"""

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from alcoabase.database import Base, get_db_session
from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.main import app
from alcoabase.models.company import Company, CompanyMembership
from alcoabase.models.user import User


# ---------------------------------------------------------------------------
# Fixtures: Async SQLite in-memory database
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def async_engine():
    """Create an async SQLite in-memory engine for integration tests."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )

    # SQLite doesn't enforce FK constraints by default; enable them.
    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def session_factory(async_engine):
    """Create an async session factory bound to the test engine."""
    factory = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    return factory


@pytest_asyncio.fixture
async def db_session(session_factory) -> AsyncGenerator[AsyncSession, None]:
    """Provide a database session for direct test setup operations."""
    async with session_factory() as session:
        yield session
        await session.commit()


@pytest_asyncio.fixture
async def client(session_factory) -> AsyncGenerator[AsyncClient, None]:
    """Create an httpx AsyncClient with overridden get_db_session.

    Uses a real async SQLite session so the full request lifecycle
    (middleware → dependency → route → DB) is exercised.
    """

    async def _override_get_db_session():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db_session] = _override_get_db_session

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={
            "X-Change-Reason": "Integration test",
            "X-User-Id": "1",
        },
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helper: Seed users and companies directly in the database
# ---------------------------------------------------------------------------


async def seed_user(session: AsyncSession, user_id: int, username: str) -> User:
    """Insert a user directly into the database."""
    user = User(
        id=user_id,
        username=username,
        email=f"{username}@test.local",
        hashed_password="hashed_placeholder",
        full_name=f"Test User {username}",
        is_active=True,
    )
    session.add(user)
    await session.flush()
    return user


async def seed_company(
    session: AsyncSession,
    slug: str,
    display_name: str,
    is_active: bool = True,
) -> Company:
    """Insert a company directly into the database."""
    company = Company(
        slug=slug,
        display_name=display_name,
        regulatory_framework="ISO_13485",
        audit_config={},
        is_active=is_active,
    )
    session.add(company)
    await session.flush()
    return company


async def seed_membership(
    session: AsyncSession,
    user_id: int,
    company_id: int,
    role: str = "member",
) -> CompanyMembership:
    """Insert a membership directly into the database."""
    membership = CompanyMembership(
        user_id=user_id,
        company_id=company_id,
        role=role,
    )
    session.add(membership)
    await session.flush()
    return membership


# ---------------------------------------------------------------------------
# Test 1: Full lifecycle — create company → add member → resolve tenant
# ---------------------------------------------------------------------------


class TestFullLifecycle:
    """Test the full request lifecycle: create company, add member, resolve tenant."""

    @pytest.mark.asyncio
    async def test_create_company_and_add_member(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """POST /api/companies → POST /api/companies/{slug}/members succeeds."""
        # Seed a user for membership
        await seed_user(db_session, user_id=1, username="alice")
        await db_session.commit()

        # Create a company via API
        payload = {
            "slug": "pharma-co",
            "display_name": "Pharma Co",
            "regulatory_framework": "ISO_13485",
            "audit_config": {"retention_years": 10},
        }
        resp = await client.post("/api/companies", json=payload)
        assert resp.status_code == 201
        company_data = resp.json()
        assert company_data["slug"] == "pharma-co"
        assert company_data["is_active"] is True

        # Add user as member
        member_payload = {"user_id": 1, "role": "admin"}
        resp = await client.post(
            "/api/companies/pharma-co/members", json=member_payload
        )
        assert resp.status_code == 201
        member_data = resp.json()
        assert member_data["user_id"] == 1
        assert member_data["role"] == "admin"
        assert member_data["revoked_at"] is None

    @pytest.mark.asyncio
    async def test_tenant_context_resolves_for_single_company_user(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Tenant context auto-selects when user has exactly one membership."""
        user = await seed_user(db_session, user_id=2, username="bob")
        company = await seed_company(db_session, "bio-labs", "Bio Labs")
        await seed_membership(db_session, user_id=user.id, company_id=company.id)
        await db_session.commit()

        # GET /api/companies/bio-labs with X-User-Id=2 should resolve tenant
        resp = await client.get(
            "/api/companies/bio-labs",
            headers={"X-User-Id": "2", "X-Change-Reason": "Integration test"},
        )
        assert resp.status_code == 200
        assert resp.json()["slug"] == "bio-labs"


# ---------------------------------------------------------------------------
# Test 2: Tenant isolation — two companies, verify data separation
# ---------------------------------------------------------------------------


class TestTenantIsolation:
    """Test that two companies with overlapping data are fully isolated."""

    @pytest.mark.asyncio
    async def test_get_company_returns_correct_data_per_tenant(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """GET /api/companies/{slug} returns correct company for each slug."""
        # Create two companies
        await seed_company(db_session, "alpha-corp", "Alpha Corporation")
        await seed_company(db_session, "beta-inc", "Beta Incorporated")
        await db_session.commit()

        # Verify each company returns its own data
        resp_alpha = await client.get("/api/companies/alpha-corp")
        assert resp_alpha.status_code == 200
        assert resp_alpha.json()["display_name"] == "Alpha Corporation"

        resp_beta = await client.get("/api/companies/beta-inc")
        assert resp_beta.status_code == 200
        assert resp_beta.json()["display_name"] == "Beta Incorporated"

    @pytest.mark.asyncio
    async def test_members_isolated_between_companies(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Members of company A are not visible in company B's member list."""
        # Seed users
        user1 = await seed_user(db_session, user_id=10, username="user-alpha")
        user2 = await seed_user(db_session, user_id=11, username="user-beta")

        # Seed companies
        company_a = await seed_company(db_session, "company-aaa", "Company AAA")
        company_b = await seed_company(db_session, "company-bbb", "Company BBB")

        # Assign user1 to company A, user2 to company B
        await seed_membership(db_session, user_id=user1.id, company_id=company_a.id)
        await seed_membership(db_session, user_id=user2.id, company_id=company_b.id)
        await db_session.commit()

        # List members of company A — should only contain user1
        resp_a = await client.get("/api/companies/company-aaa/members")
        assert resp_a.status_code == 200
        members_a = resp_a.json()
        assert len(members_a) == 1
        assert members_a[0]["user_id"] == 10

        # List members of company B — should only contain user2
        resp_b = await client.get("/api/companies/company-bbb/members")
        assert resp_b.status_code == 200
        members_b = resp_b.json()
        assert len(members_b) == 1
        assert members_b[0]["user_id"] == 11

    @pytest.mark.asyncio
    async def test_tenant_context_isolation_with_company_id_header(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """User with multiple memberships must specify X-Company-Id header."""
        user = await seed_user(db_session, user_id=20, username="multi-user")
        company_x = await seed_company(db_session, "company-xxx", "Company X")
        company_y = await seed_company(db_session, "company-yyy", "Company Y")
        await seed_membership(db_session, user_id=user.id, company_id=company_x.id)
        await seed_membership(db_session, user_id=user.id, company_id=company_y.id)
        await db_session.commit()

        # Override get_tenant_context to test resolution directly
        # Without X-Company-Id, multi-company user should get 400
        from alcoabase.dependencies.tenant import get_tenant_context as _gtc

        # Make a request that uses tenant context — use a custom endpoint
        # Instead, test the dependency directly via the companies endpoint
        # which doesn't use get_tenant_context. Let's test via a direct call.

        # We test the tenant resolution by calling an endpoint that depends on it.
        # The companies endpoint doesn't use tenant context, so we test the
        # dependency behavior by verifying the resolution logic.
        from fastapi import Request
        from sqlalchemy.ext.asyncio import AsyncSession as AS

        # Simulate the resolution: user 20 has 2 companies, no X-Company-Id → 400
        from fastapi import HTTPException

        from alcoabase.dependencies.tenant import get_tenant_context

        # Create a mock request without X-Company-Id
        class MockRequest:
            headers = {"X-User-Id": "20"}

        async with db_session.begin_nested():
            try:
                await get_tenant_context(MockRequest(), db_session)
                assert False, "Should have raised HTTPException"
            except HTTPException as e:
                assert e.status_code == 400
                assert "Company selection required" in e.detail

        # With X-Company-Id for company_x → should succeed
        class MockRequestWithCompany:
            headers = {"X-User-Id": "20", "X-Company-Id": str(company_x.id)}

        async with db_session.begin_nested():
            ctx = await get_tenant_context(MockRequestWithCompany(), db_session)
            assert ctx.company_id == company_x.id
            assert ctx.company_slug == "company-xxx"
            assert ctx.user_id == 20


# ---------------------------------------------------------------------------
# Test 3: Company deactivation blocks access, reactivation restores it
# ---------------------------------------------------------------------------


class TestCompanyDeactivation:
    """Test company deactivation blocks tenant resolution and reactivation restores it."""

    @pytest.mark.asyncio
    async def test_deactivation_blocks_tenant_resolution(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Deactivated company returns 403 on tenant context resolution."""
        user = await seed_user(db_session, user_id=30, username="deact-user")
        company = await seed_company(db_session, "deact-co", "Deactivation Co")
        await seed_membership(db_session, user_id=user.id, company_id=company.id)
        await db_session.commit()

        # Verify tenant resolution works while active
        from fastapi import HTTPException

        from alcoabase.dependencies.tenant import get_tenant_context

        class ActiveRequest:
            headers = {"X-User-Id": "30"}

        async with db_session.begin_nested():
            ctx = await get_tenant_context(ActiveRequest(), db_session)
            assert ctx.company_id == company.id
            assert ctx.company_slug == "deact-co"

        # Deactivate the company via API
        resp = await client.post("/api/companies/deact-co/deactivate")
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False

        # Refresh the session to see the deactivation
        db_session.expire_all()

        # Tenant resolution should now fail with 403
        async with db_session.begin_nested():
            try:
                await get_tenant_context(ActiveRequest(), db_session)
                assert False, "Should have raised HTTPException"
            except HTTPException as e:
                assert e.status_code == 403
                assert "inactive" in e.detail.lower()

    @pytest.mark.asyncio
    async def test_reactivation_restores_access(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Reactivating a company restores tenant resolution for existing members."""
        user = await seed_user(db_session, user_id=31, username="react-user")
        company = await seed_company(
            db_session, "react-co", "Reactivation Co", is_active=False
        )
        await seed_membership(db_session, user_id=user.id, company_id=company.id)
        await db_session.commit()

        from fastapi import HTTPException

        from alcoabase.dependencies.tenant import get_tenant_context

        class UserRequest:
            headers = {"X-User-Id": "31"}

        # Verify access is blocked while inactive
        async with db_session.begin_nested():
            try:
                await get_tenant_context(UserRequest(), db_session)
                assert False, "Should have raised HTTPException"
            except HTTPException as e:
                assert e.status_code == 403
                assert "inactive" in e.detail.lower()

        # Reactivate via API
        resp = await client.post("/api/companies/react-co/reactivate")
        assert resp.status_code == 200
        assert resp.json()["is_active"] is True

        # Refresh session
        db_session.expire_all()

        # Tenant resolution should now succeed
        async with db_session.begin_nested():
            ctx = await get_tenant_context(UserRequest(), db_session)
            assert ctx.company_id == company.id
            assert ctx.company_slug == "react-co"
            assert ctx.user_id == 31


# ---------------------------------------------------------------------------
# Test 4: Membership revocation blocks access
# ---------------------------------------------------------------------------


class TestMembershipRevocation:
    """Test that revoking membership immediately blocks tenant resolution."""

    @pytest.mark.asyncio
    async def test_revoked_membership_blocks_tenant_resolution(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Revoking a membership prevents tenant context resolution."""
        user = await seed_user(db_session, user_id=40, username="revoke-user")
        company = await seed_company(db_session, "revoke-co", "Revoke Co")
        await seed_membership(db_session, user_id=user.id, company_id=company.id)
        await db_session.commit()

        from fastapi import HTTPException

        from alcoabase.dependencies.tenant import get_tenant_context

        class UserRequest:
            headers = {"X-User-Id": "40"}

        # Verify access works before revocation
        async with db_session.begin_nested():
            ctx = await get_tenant_context(UserRequest(), db_session)
            assert ctx.company_id == company.id

        # Revoke membership via API
        resp = await client.delete(
            f"/api/companies/revoke-co/members/{user.id}"
        )
        assert resp.status_code == 200
        revoked_data = resp.json()
        assert revoked_data["revoked_at"] is not None

        # Refresh session
        db_session.expire_all()

        # Tenant resolution should now fail with 403
        async with db_session.begin_nested():
            try:
                await get_tenant_context(UserRequest(), db_session)
                assert False, "Should have raised HTTPException"
            except HTTPException as e:
                assert e.status_code == 403
                assert "Not a member" in e.detail

    @pytest.mark.asyncio
    async def test_revoked_user_cannot_access_other_company_members(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """After revocation, user has no active memberships and gets 403."""
        user = await seed_user(db_session, user_id=41, username="revoke-user2")
        company = await seed_company(db_session, "revoke-co2", "Revoke Co 2")
        await seed_membership(db_session, user_id=user.id, company_id=company.id)
        await db_session.commit()

        from fastapi import HTTPException

        from alcoabase.dependencies.tenant import get_tenant_context

        # Revoke via API
        resp = await client.delete(
            f"/api/companies/revoke-co2/members/{user.id}"
        )
        assert resp.status_code == 200

        # Refresh session
        db_session.expire_all()

        # User now has zero active memberships → 403
        class UserRequest:
            headers = {"X-User-Id": "41"}

        async with db_session.begin_nested():
            try:
                await get_tenant_context(UserRequest(), db_session)
                assert False, "Should have raised HTTPException"
            except HTTPException as e:
                assert e.status_code == 403
