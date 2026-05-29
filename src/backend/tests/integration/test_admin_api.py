"""Integration tests for admin API endpoints (Phase 6.1).

Tests the full admin user management lifecycle through the API layer
using httpx.AsyncClient with an async SQLite in-memory database.

Covers:
- Full user lifecycle: create → assign role → verify access → deactivate → verify denial → reactivate
- admin_users endpoints (HTTP status codes, pagination, search, sort)
- admin_roles endpoints (list with counts, detail with permission matrix)
- admin_permission_templates endpoints (CRUD, deletion guard)
- admin_memberships endpoints (assign, revoke soft-delete, list)
- X-Change-Reason enforcement on all mutation endpoints
- Error responses (403, 404, 409, 422)
- Multi-company permission isolation end-to-end

References:
    - Task 10.6: Write integration tests for admin API endpoints
    - Requirements: 1.1–14.3 (all requirements)
"""

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sqlalchemy.orm import configure_mappers

from alcoabase.database import Base, get_db_session
from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.main import app
from alcoabase.models.company import Company, CompanyMembership
from alcoabase.models.permission_template import PermissionTemplate  # noqa: F401
from alcoabase.models.refresh_token import RefreshToken  # noqa: F401
from alcoabase.models.user import Role, User
from alcoabase.services.rbac import DEFAULT_ROLE_PERMISSIONS

# Ensure all mappers (including Continuum version tables) are configured
configure_mappers()

# Tables required for admin API integration tests (avoids creating all tables
# which may use PostgreSQL-specific types like JSONB that SQLite cannot handle)
_REQUIRED_TABLE_NAMES = [
    "users",
    "companies",
    "company_memberships",
    "roles",
    "permission_templates",
    "refresh_tokens",
    "documents",
    "transaction",
]
# Also include version tables if they exist
for _name in list(_REQUIRED_TABLE_NAMES):
    _version_name = f"{_name}_version"
    if _version_name in Base.metadata.tables:
        _REQUIRED_TABLE_NAMES.append(_version_name)

_REQUIRED_TABLES = [
    Base.metadata.tables[name]
    for name in _REQUIRED_TABLE_NAMES
    if name in Base.metadata.tables
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def async_engine():
    """Create an async SQLite in-memory engine for integration tests."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )

    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all, tables=_REQUIRED_TABLES
        )

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def session_factory(async_engine):
    """Create an async session factory bound to the test engine."""
    return async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


@pytest_asyncio.fixture
async def db_session(session_factory) -> AsyncGenerator[AsyncSession, None]:
    """Provide a database session for direct test setup operations."""
    async with session_factory() as session:
        yield session
        await session.commit()


@pytest_asyncio.fixture
async def seeded_data(db_session: AsyncSession) -> dict:
    """Seed a company, admin user, roles, and memberships for testing.

    Returns a dict with company, admin_user, roles, and membership references.
    """
    # Create company
    company = Company(
        id=1,
        slug="test-pharma",
        display_name="Test Pharma Inc",
        regulatory_framework="ISO_13485",
        audit_config={},
        is_active=True,
    )
    db_session.add(company)
    await db_session.flush()

    # Create admin user
    admin_user = User(
        id=1,
        username="admin_user",
        email="admin@example.com",
        hashed_password="hashed_placeholder",
        full_name="Admin User",
        is_active=True,
    )
    db_session.add(admin_user)
    await db_session.flush()

    # Seed default roles for the company
    roles = {}
    for role_name, permissions in DEFAULT_ROLE_PERMISSIONS.items():
        role = Role(
            name=role_name,
            description=f"{role_name} role",
            permissions=permissions,
            company_id=company.id,
            is_system=True,
        )
        db_session.add(role)
        await db_session.flush()
        roles[role_name] = role

    # Create admin membership with system_admin role
    admin_membership = CompanyMembership(
        user_id=admin_user.id,
        company_id=company.id,
        role="system_admin",
        role_id=roles["system_admin"].id,
    )
    db_session.add(admin_membership)
    await db_session.flush()
    await db_session.commit()

    return {
        "company": company,
        "admin_user": admin_user,
        "roles": roles,
        "admin_membership": admin_membership,
    }


@pytest_asyncio.fixture
async def client(session_factory, seeded_data) -> AsyncGenerator[AsyncClient, None]:
    """Create an httpx AsyncClient with overridden dependencies.

    Overrides get_db_session and get_tenant_context so the full request
    lifecycle (middleware → dependency → route → DB) is exercised against
    the in-memory SQLite database.
    """

    async def _override_get_db_session():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    # Override tenant context to simulate an authenticated system_admin
    async def _override_get_tenant_context():
        return TenantContext(
            company_id=1,
            company_slug="test-pharma",
            user_id=1,
            membership_role="system_admin",
        )

    app.dependency_overrides[get_db_session] = _override_get_db_session
    app.dependency_overrides[get_tenant_context] = _override_get_tenant_context

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={
            "X-Change-Reason": "Integration test",
            "X-User-Id": "1",
            "X-Company-Id": "1",
        },
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def viewer_client(
    session_factory, seeded_data, db_session: AsyncSession
) -> AsyncGenerator[AsyncClient, None]:
    """Create a client authenticated as a viewer (limited permissions)."""
    # Create a viewer user
    viewer = User(
        id=50,
        username="viewer_user",
        email="viewer@example.com",
        hashed_password="hashed_placeholder",
        full_name="Viewer User",
        is_active=True,
    )
    db_session.add(viewer)
    await db_session.flush()

    roles = seeded_data["roles"]
    membership = CompanyMembership(
        user_id=viewer.id,
        company_id=1,
        role="viewer",
        role_id=roles["viewer"].id,
    )
    db_session.add(membership)
    await db_session.flush()
    await db_session.commit()

    async def _override_get_db_session():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def _override_get_tenant_context():
        return TenantContext(
            company_id=1,
            company_slug="test-pharma",
            user_id=50,
            membership_role="viewer",
        )

    app.dependency_overrides[get_db_session] = _override_get_db_session
    app.dependency_overrides[get_tenant_context] = _override_get_tenant_context

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={
            "X-Change-Reason": "Integration test",
            "X-User-Id": "50",
            "X-Company-Id": "1",
        },
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Test: Full User Lifecycle
# ---------------------------------------------------------------------------


class TestFullUserLifecycle:
    """Test the complete user lifecycle: create → role → access → deactivate → reactivate."""

    @pytest.mark.asyncio
    async def test_create_assign_deactivate_reactivate(
        self, client: AsyncClient
    ) -> None:
        """Full lifecycle: create user, verify access, deactivate, reactivate."""
        # 1. Create a new user
        create_payload = {
            "username": "lifecycle_user",
            "email": "lifecycle@example.com",
            "full_name": "Lifecycle User",
            "role": "member",
        }
        resp = await client.post("/api/admin/users", json=create_payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["username"] == "lifecycle_user"
        assert data["role"] == "member"
        assert data["is_active"] is True
        assert "temporary_password" in data
        user_id = data["id"]

        # 2. Verify user detail
        resp = await client.get(f"/api/admin/users/{user_id}")
        assert resp.status_code == 200
        detail = resp.json()
        assert detail["username"] == "lifecycle_user"
        assert detail["is_active"] is True
        assert len(detail["memberships"]) == 1
        assert detail["memberships"][0]["role"] == "member"

        # 3. Update user role
        update_payload = {"role": "doc_admin"}
        resp = await client.patch(
            f"/api/admin/users/{user_id}", json=update_payload
        )
        assert resp.status_code == 200
        updated = resp.json()
        # Verify membership role updated
        assert any(m["role"] == "doc_admin" for m in updated["memberships"])

        # 4. Deactivate user
        resp = await client.post(f"/api/admin/users/{user_id}/deactivate")
        assert resp.status_code == 200
        deactivated = resp.json()
        assert deactivated["is_active"] is False

        # 5. Reactivate user
        resp = await client.post(f"/api/admin/users/{user_id}/reactivate")
        assert resp.status_code == 200
        reactivated = resp.json()
        assert reactivated["is_active"] is True


# ---------------------------------------------------------------------------
# Test: Admin Users Endpoints
# ---------------------------------------------------------------------------


class TestAdminUsersEndpoints:
    """Test all admin_users endpoints with database."""

    @pytest.mark.asyncio
    async def test_list_users_returns_paginated(
        self, client: AsyncClient
    ) -> None:
        """GET /api/admin/users returns paginated user list."""
        resp = await client.get("/api/admin/users")
        assert resp.status_code == 200
        data = resp.json()
        assert "users" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert "total_pages" in data
        assert data["page"] == 1
        assert data["total"] >= 1  # At least the admin user

    @pytest.mark.asyncio
    async def test_list_users_pagination(self, client: AsyncClient) -> None:
        """GET /api/admin/users respects page_size parameter."""
        # Create a few users first
        for i in range(3):
            await client.post(
                "/api/admin/users",
                json={
                    "username": f"page_user_{i}",
                    "email": f"page{i}@example.com",
                    "full_name": f"Page User {i}",
                    "role": "member",
                },
            )

        resp = await client.get("/api/admin/users?page_size=2&page=1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["users"]) <= 2
        assert data["page_size"] == 2

    @pytest.mark.asyncio
    async def test_list_users_search(self, client: AsyncClient) -> None:
        """GET /api/admin/users?search= filters by username/email/full_name."""
        # Create a user with a unique name
        await client.post(
            "/api/admin/users",
            json={
                "username": "searchable_xyz",
                "email": "searchxyz@example.com",
                "full_name": "Searchable XYZ User",
                "role": "member",
            },
        )

        resp = await client.get("/api/admin/users?search=searchable_xyz")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        assert any(u["username"] == "searchable_xyz" for u in data["users"])

    @pytest.mark.asyncio
    async def test_list_users_sort(self, client: AsyncClient) -> None:
        """GET /api/admin/users supports sorting by username asc/desc."""
        resp = await client.get(
            "/api/admin/users?sort_by=username&sort_dir=asc"
        )
        assert resp.status_code == 200
        data = resp.json()
        usernames = [u["username"] for u in data["users"]]
        assert usernames == sorted(usernames)

    @pytest.mark.asyncio
    async def test_create_user_success(self, client: AsyncClient) -> None:
        """POST /api/admin/users creates user and returns 201."""
        payload = {
            "username": "new_user_create",
            "email": "newcreate@example.com",
            "full_name": "New Create User",
            "role": "member",
        }
        resp = await client.post("/api/admin/users", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["username"] == "new_user_create"
        assert data["email"] == "newcreate@example.com"
        assert data["full_name"] == "New Create User"
        assert data["role"] == "member"
        assert data["is_active"] is True
        assert len(data["temporary_password"]) > 0

    @pytest.mark.asyncio
    async def test_create_user_duplicate_username_409(
        self, client: AsyncClient
    ) -> None:
        """POST /api/admin/users returns 409 for duplicate username."""
        payload = {
            "username": "dup_user",
            "email": "dup1@example.com",
            "full_name": "Dup User",
            "role": "member",
        }
        resp = await client.post("/api/admin/users", json=payload)
        assert resp.status_code == 201

        # Try to create again with same username
        payload["email"] = "dup2@example.com"
        resp = await client.post("/api/admin/users", json=payload)
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_create_user_duplicate_email_409(
        self, client: AsyncClient
    ) -> None:
        """POST /api/admin/users returns 409 for duplicate email."""
        payload = {
            "username": "email_dup1",
            "email": "same_email@example.com",
            "full_name": "Email Dup 1",
            "role": "member",
        }
        resp = await client.post("/api/admin/users", json=payload)
        assert resp.status_code == 201

        payload["username"] = "email_dup2"
        resp = await client.post("/api/admin/users", json=payload)
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_get_user_detail(self, client: AsyncClient) -> None:
        """GET /api/admin/users/{id} returns user detail with memberships."""
        # Create a user first
        resp = await client.post(
            "/api/admin/users",
            json={
                "username": "detail_user",
                "email": "detail@example.com",
                "full_name": "Detail User",
                "role": "member",
            },
        )
        user_id = resp.json()["id"]

        resp = await client.get(f"/api/admin/users/{user_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == user_id
        assert data["username"] == "detail_user"
        assert "memberships" in data
        assert len(data["memberships"]) >= 1

    @pytest.mark.asyncio
    async def test_get_user_not_found_404(self, client: AsyncClient) -> None:
        """GET /api/admin/users/{id} returns 404 for non-existent user."""
        resp = await client.get("/api/admin/users/99999")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_user(self, client: AsyncClient) -> None:
        """PATCH /api/admin/users/{id} updates user profile."""
        resp = await client.post(
            "/api/admin/users",
            json={
                "username": "update_target",
                "email": "update_target@example.com",
                "full_name": "Update Target",
                "role": "member",
            },
        )
        user_id = resp.json()["id"]

        resp = await client.patch(
            f"/api/admin/users/{user_id}",
            json={"full_name": "Updated Name", "email": "updated@example.com"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["full_name"] == "Updated Name"
        assert data["email"] == "updated@example.com"

    @pytest.mark.asyncio
    async def test_deactivate_user(self, client: AsyncClient) -> None:
        """POST /api/admin/users/{id}/deactivate sets is_active=False."""
        resp = await client.post(
            "/api/admin/users",
            json={
                "username": "deact_target",
                "email": "deact@example.com",
                "full_name": "Deact Target",
                "role": "member",
            },
        )
        user_id = resp.json()["id"]

        resp = await client.post(f"/api/admin/users/{user_id}/deactivate")
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False

    @pytest.mark.asyncio
    async def test_self_deactivation_422(self, client: AsyncClient) -> None:
        """POST /api/admin/users/{id}/deactivate returns 422 for self."""
        # Admin user (id=1) tries to deactivate themselves
        resp = await client.post("/api/admin/users/1/deactivate")
        assert resp.status_code == 422
        assert "own account" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_reactivate_user(self, client: AsyncClient) -> None:
        """POST /api/admin/users/{id}/reactivate restores is_active=True."""
        resp = await client.post(
            "/api/admin/users",
            json={
                "username": "react_target",
                "email": "react@example.com",
                "full_name": "React Target",
                "role": "member",
            },
        )
        user_id = resp.json()["id"]

        # Deactivate first
        await client.post(f"/api/admin/users/{user_id}/deactivate")

        # Reactivate
        resp = await client.post(f"/api/admin/users/{user_id}/reactivate")
        assert resp.status_code == 200
        assert resp.json()["is_active"] is True

    @pytest.mark.asyncio
    async def test_reset_password(self, client: AsyncClient) -> None:
        """POST /api/admin/users/{id}/reset-password returns temp password."""
        resp = await client.post(
            "/api/admin/users",
            json={
                "username": "reset_target",
                "email": "reset@example.com",
                "full_name": "Reset Target",
                "role": "member",
            },
        )
        user_id = resp.json()["id"]

        resp = await client.post(f"/api/admin/users/{user_id}/reset-password")
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == user_id
        assert len(data["temporary_password"]) > 0


# ---------------------------------------------------------------------------
# Test: Admin Roles Endpoints
# ---------------------------------------------------------------------------


class TestAdminRolesEndpoints:
    """Test admin_roles endpoints (list with counts, detail with permission matrix)."""

    @pytest.mark.asyncio
    async def test_list_roles(self, client: AsyncClient) -> None:
        """GET /api/admin/roles returns all roles with user counts."""
        resp = await client.get("/api/admin/roles")
        assert resp.status_code == 200
        data = resp.json()
        assert "roles" in data
        roles = data["roles"]
        assert len(roles) == 5  # system_admin, doc_admin, it_admin, member, viewer

        role_names = {r["name"] for r in roles}
        assert role_names == {
            "system_admin",
            "doc_admin",
            "it_admin",
            "member",
            "viewer",
        }

        # Each role should have user_count field
        for role in roles:
            assert "user_count" in role
            assert "is_system" in role
            assert role["is_system"] is True

    @pytest.mark.asyncio
    async def test_list_roles_user_count(self, client: AsyncClient) -> None:
        """GET /api/admin/roles shows correct user count for system_admin."""
        resp = await client.get("/api/admin/roles")
        data = resp.json()
        # The admin user has system_admin role
        sa_role = next(r for r in data["roles"] if r["name"] == "system_admin")
        assert sa_role["user_count"] >= 1

    @pytest.mark.asyncio
    async def test_get_role_detail(
        self, client: AsyncClient, seeded_data: dict
    ) -> None:
        """GET /api/admin/roles/{id} returns role with permission matrix."""
        role_id = seeded_data["roles"]["system_admin"].id
        resp = await client.get(f"/api/admin/roles/{role_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "system_admin"
        assert data["is_system"] is True
        assert "permissions" in data
        # system_admin should have all resources
        assert "documents" in data["permissions"]
        assert "create" in data["permissions"]["documents"]
        assert "user_count" in data

    @pytest.mark.asyncio
    async def test_get_role_not_found_404(self, client: AsyncClient) -> None:
        """GET /api/admin/roles/{id} returns 404 for non-existent role."""
        resp = await client.get("/api/admin/roles/99999")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test: Admin Permission Templates Endpoints
# ---------------------------------------------------------------------------


class TestAdminPermissionTemplatesEndpoints:
    """Test admin_permission_templates endpoints (CRUD, deletion guard)."""

    @pytest.mark.asyncio
    async def test_create_permission_template(
        self, client: AsyncClient
    ) -> None:
        """POST /api/admin/permission-templates creates template."""
        payload = {
            "name": "Test SOP Template",
            "description": "Template for test SOPs",
            "document_type": "SOP",
            "role_permissions": [
                {"role": "system_admin", "actions": ["read", "write", "approve"]},
                {"role": "doc_admin", "actions": ["read", "write", "approve"]},
                {"role": "member", "actions": ["read"]},
                {"role": "viewer", "actions": ["read"]},
            ],
        }
        resp = await client.post(
            "/api/admin/permission-templates", json=payload
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Test SOP Template"
        assert data["document_type"] == "SOP"
        assert "role_permissions" in data
        assert data["is_default"] is False

    @pytest.mark.asyncio
    async def test_list_permission_templates(
        self, client: AsyncClient
    ) -> None:
        """GET /api/admin/permission-templates returns template list."""
        # Create a template first
        await client.post(
            "/api/admin/permission-templates",
            json={
                "name": "List Test Template",
                "document_type": "Protocol",
                "role_permissions": [
                    {"role": "system_admin", "actions": ["read", "write"]},
                ],
            },
        )

        resp = await client.get("/api/admin/permission-templates")
        assert resp.status_code == 200
        data = resp.json()
        assert "templates" in data
        assert len(data["templates"]) >= 1

    @pytest.mark.asyncio
    async def test_get_permission_template_detail(
        self, client: AsyncClient
    ) -> None:
        """GET /api/admin/permission-templates/{id} returns template detail."""
        # Create a template
        resp = await client.post(
            "/api/admin/permission-templates",
            json={
                "name": "Detail Test Template",
                "description": "For detail test",
                "document_type": "Report",
                "role_permissions": [
                    {"role": "doc_admin", "actions": ["read", "write", "approve"]},
                ],
            },
        )
        template_id = resp.json()["id"]

        resp = await client.get(
            f"/api/admin/permission-templates/{template_id}"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == template_id
        assert data["name"] == "Detail Test Template"
        assert data["document_type"] == "Report"

    @pytest.mark.asyncio
    async def test_update_permission_template(
        self, client: AsyncClient
    ) -> None:
        """PATCH /api/admin/permission-templates/{id} updates template."""
        resp = await client.post(
            "/api/admin/permission-templates",
            json={
                "name": "Update Test Template",
                "document_type": "Form",
                "role_permissions": [
                    {"role": "member", "actions": ["read"]},
                ],
            },
        )
        template_id = resp.json()["id"]

        resp = await client.patch(
            f"/api/admin/permission-templates/{template_id}",
            json={"name": "Updated Template Name"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Template Name"

    @pytest.mark.asyncio
    async def test_delete_permission_template_no_docs(
        self, client: AsyncClient
    ) -> None:
        """DELETE /api/admin/permission-templates/{id} succeeds with no active docs."""
        resp = await client.post(
            "/api/admin/permission-templates",
            json={
                "name": "Delete Test Template",
                "document_type": "Memo",
                "role_permissions": [
                    {"role": "viewer", "actions": ["read"]},
                ],
            },
        )
        template_id = resp.json()["id"]

        resp = await client.delete(
            f"/api/admin/permission-templates/{template_id}"
        )
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_permission_template_not_found_404(
        self, client: AsyncClient
    ) -> None:
        """DELETE /api/admin/permission-templates/{id} returns 404 for missing."""
        resp = await client.delete("/api/admin/permission-templates/99999")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_create_duplicate_template_name_409(
        self, client: AsyncClient
    ) -> None:
        """POST /api/admin/permission-templates returns 409 for duplicate name."""
        payload = {
            "name": "Unique Template Name",
            "document_type": "SOP",
            "role_permissions": [
                {"role": "member", "actions": ["read"]},
            ],
        }
        resp = await client.post(
            "/api/admin/permission-templates", json=payload
        )
        assert resp.status_code == 201

        # Try to create again with same name
        resp = await client.post(
            "/api/admin/permission-templates", json=payload
        )
        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Test: Admin Memberships Endpoints
# ---------------------------------------------------------------------------


class TestAdminMembershipsEndpoints:
    """Test admin_memberships endpoints (assign, revoke soft-delete, list)."""

    @pytest.mark.asyncio
    async def test_assign_membership(self, client: AsyncClient) -> None:
        """POST /api/admin/memberships assigns user to company."""
        # Create a second company for cross-company assignment
        # First create a user without membership in company 1
        resp = await client.post(
            "/api/admin/users",
            json={
                "username": "membership_user",
                "email": "membership@example.com",
                "full_name": "Membership User",
                "role": "member",
            },
        )
        assert resp.status_code == 201
        user_id = resp.json()["id"]

        # List memberships for this user
        resp = await client.get(f"/api/admin/memberships/user/{user_id}")
        assert resp.status_code == 200
        memberships = resp.json()
        assert len(memberships) >= 1
        assert memberships[0]["user_id"] == user_id

    @pytest.mark.asyncio
    async def test_revoke_membership_soft_delete(
        self, client: AsyncClient
    ) -> None:
        """DELETE /api/admin/memberships/{id} sets revoked_at (soft delete)."""
        # Create a user
        resp = await client.post(
            "/api/admin/users",
            json={
                "username": "revoke_member",
                "email": "revoke_member@example.com",
                "full_name": "Revoke Member",
                "role": "member",
            },
        )
        user_id = resp.json()["id"]

        # Get the membership ID
        resp = await client.get(f"/api/admin/memberships/user/{user_id}")
        memberships = resp.json()
        membership_id = memberships[0]["id"]

        # Revoke the membership
        resp = await client.delete(
            f"/api/admin/memberships/{membership_id}"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["revoked_at"] is not None

        # Verify it still appears in the list (soft delete)
        resp = await client.get(f"/api/admin/memberships/user/{user_id}")
        memberships = resp.json()
        revoked = [m for m in memberships if m["revoked_at"] is not None]
        assert len(revoked) >= 1

    @pytest.mark.asyncio
    async def test_assign_duplicate_membership_409(
        self, client: AsyncClient
    ) -> None:
        """POST /api/admin/memberships returns 409 for duplicate active membership."""
        # Create a user (already has membership in company 1)
        resp = await client.post(
            "/api/admin/users",
            json={
                "username": "dup_member",
                "email": "dup_member@example.com",
                "full_name": "Dup Member",
                "role": "member",
            },
        )
        user_id = resp.json()["id"]

        # Try to assign again to same company
        resp = await client.post(
            "/api/admin/memberships",
            json={
                "user_id": user_id,
                "company_id": 1,
                "role": "viewer",
            },
        )
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_list_memberships_for_user(
        self, client: AsyncClient
    ) -> None:
        """GET /api/admin/memberships/user/{id} returns all memberships."""
        resp = await client.get("/api/admin/memberships/user/1")
        assert resp.status_code == 200
        memberships = resp.json()
        assert len(memberships) >= 1
        assert memberships[0]["user_id"] == 1
        assert "company_name" in memberships[0]
        assert "role" in memberships[0]
        assert "created_at" in memberships[0]


# ---------------------------------------------------------------------------
# Test: X-Change-Reason Enforcement
# ---------------------------------------------------------------------------


class TestXChangeReasonEnforcement:
    """Test X-Change-Reason header enforcement on all mutation endpoints."""

    @pytest_asyncio.fixture
    async def no_reason_client(
        self, session_factory, seeded_data
    ) -> AsyncGenerator[AsyncClient, None]:
        """Client WITHOUT X-Change-Reason header."""

        async def _override_get_db_session():
            async with session_factory() as session:
                try:
                    yield session
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise

        async def _override_get_tenant_context():
            return TenantContext(
                company_id=1,
                company_slug="test-pharma",
                user_id=1,
                membership_role="system_admin",
            )

        app.dependency_overrides[get_db_session] = _override_get_db_session
        app.dependency_overrides[get_tenant_context] = _override_get_tenant_context

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={
                "X-User-Id": "1",
                "X-Company-Id": "1",
                # No X-Change-Reason header!
            },
        ) as ac:
            yield ac

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_create_user_requires_change_reason(
        self, no_reason_client: AsyncClient
    ) -> None:
        """POST /api/admin/users returns 400 without X-Change-Reason."""
        resp = await no_reason_client.post(
            "/api/admin/users",
            json={
                "username": "no_reason_user",
                "email": "noreason@example.com",
                "full_name": "No Reason",
                "role": "member",
            },
        )
        assert resp.status_code == 400
        assert "X-Change-Reason" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_update_user_requires_change_reason(
        self, no_reason_client: AsyncClient
    ) -> None:
        """PATCH /api/admin/users/{id} returns 400 without X-Change-Reason."""
        resp = await no_reason_client.patch(
            "/api/admin/users/1",
            json={"full_name": "Updated"},
        )
        assert resp.status_code == 400
        assert "X-Change-Reason" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_deactivate_requires_change_reason(
        self, no_reason_client: AsyncClient
    ) -> None:
        """POST /api/admin/users/{id}/deactivate returns 400 without X-Change-Reason."""
        resp = await no_reason_client.post("/api/admin/users/2/deactivate")
        assert resp.status_code == 400
        assert "X-Change-Reason" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_template_requires_change_reason(
        self, no_reason_client: AsyncClient
    ) -> None:
        """POST /api/admin/permission-templates returns 400 without X-Change-Reason."""
        resp = await no_reason_client.post(
            "/api/admin/permission-templates",
            json={
                "name": "No Reason Template",
                "document_type": "SOP",
                "role_permissions": [
                    {"role": "member", "actions": ["read"]},
                ],
            },
        )
        assert resp.status_code == 400
        assert "X-Change-Reason" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_assign_membership_requires_change_reason(
        self, no_reason_client: AsyncClient
    ) -> None:
        """POST /api/admin/memberships returns 400 without X-Change-Reason."""
        resp = await no_reason_client.post(
            "/api/admin/memberships",
            json={"user_id": 1, "company_id": 1, "role": "member"},
        )
        assert resp.status_code == 400
        assert "X-Change-Reason" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_delete_membership_requires_change_reason(
        self, no_reason_client: AsyncClient
    ) -> None:
        """DELETE /api/admin/memberships/{id} returns 400 without X-Change-Reason."""
        resp = await no_reason_client.delete("/api/admin/memberships/1")
        assert resp.status_code == 400
        assert "X-Change-Reason" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Test: Error Responses (403, 404, 409, 422)
# ---------------------------------------------------------------------------


class TestErrorResponses:
    """Test error responses across admin endpoints."""

    @pytest.mark.asyncio
    async def test_viewer_cannot_create_user_403(
        self, viewer_client: AsyncClient
    ) -> None:
        """Viewer role cannot create users (403)."""
        resp = await viewer_client.post(
            "/api/admin/users",
            json={
                "username": "forbidden_user",
                "email": "forbidden@example.com",
                "full_name": "Forbidden User",
                "role": "member",
            },
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_viewer_cannot_update_user_403(
        self, viewer_client: AsyncClient
    ) -> None:
        """Viewer role cannot update users (403)."""
        resp = await viewer_client.patch(
            "/api/admin/users/1",
            json={"full_name": "Hacked Name"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_viewer_cannot_deactivate_user_403(
        self, viewer_client: AsyncClient
    ) -> None:
        """Viewer role cannot deactivate users (403)."""
        resp = await viewer_client.post("/api/admin/users/1/deactivate")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_viewer_cannot_create_template_403(
        self, viewer_client: AsyncClient
    ) -> None:
        """Viewer role cannot create permission templates (403)."""
        resp = await viewer_client.post(
            "/api/admin/permission-templates",
            json={
                "name": "Forbidden Template",
                "document_type": "SOP",
                "role_permissions": [
                    {"role": "member", "actions": ["read"]},
                ],
            },
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_viewer_cannot_assign_membership_403(
        self, viewer_client: AsyncClient
    ) -> None:
        """Viewer role cannot assign memberships (403)."""
        resp = await viewer_client.post(
            "/api/admin/memberships",
            json={"user_id": 1, "company_id": 1, "role": "member"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_viewer_cannot_delete_template_403(
        self, viewer_client: AsyncClient
    ) -> None:
        """Viewer role cannot delete permission templates (403)."""
        resp = await viewer_client.delete(
            "/api/admin/permission-templates/1"
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_viewer_cannot_revoke_membership_403(
        self, viewer_client: AsyncClient
    ) -> None:
        """Viewer role cannot revoke memberships (403)."""
        resp = await viewer_client.delete("/api/admin/memberships/1")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_invalid_role_in_create_422(
        self, client: AsyncClient
    ) -> None:
        """POST /api/admin/users with invalid role returns 422."""
        resp = await client.post(
            "/api/admin/users",
            json={
                "username": "invalid_role_user",
                "email": "invalidrole@example.com",
                "full_name": "Invalid Role",
                "role": "superadmin",  # Not a valid role
            },
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_username_pattern_422(
        self, client: AsyncClient
    ) -> None:
        """POST /api/admin/users with invalid username pattern returns 422."""
        resp = await client.post(
            "/api/admin/users",
            json={
                "username": "invalid user!@#",  # Invalid chars
                "email": "invalidpattern@example.com",
                "full_name": "Invalid Pattern",
                "role": "member",
            },
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Test: Multi-Company Permission Isolation
# ---------------------------------------------------------------------------


class TestMultiCompanyIsolation:
    """Test multi-company permission isolation end-to-end."""

    @pytest_asyncio.fixture
    async def two_companies(
        self, db_session: AsyncSession, seeded_data: dict
    ) -> dict:
        """Seed a second company with its own roles and user."""
        company2 = Company(
            id=2,
            slug="other-pharma",
            display_name="Other Pharma",
            regulatory_framework="GMP",
            audit_config={},
            is_active=True,
        )
        db_session.add(company2)
        await db_session.flush()

        # Seed roles for company 2
        roles2 = {}
        for role_name, permissions in DEFAULT_ROLE_PERMISSIONS.items():
            role = Role(
                name=role_name,
                description=f"{role_name} role for company 2",
                permissions=permissions,
                company_id=company2.id,
                is_system=True,
            )
            db_session.add(role)
            await db_session.flush()
            roles2[role_name] = role

        # Create a user in company 2 only
        user2 = User(
            id=100,
            username="company2_user",
            email="company2@example.com",
            hashed_password="hashed_placeholder",
            full_name="Company 2 User",
            is_active=True,
        )
        db_session.add(user2)
        await db_session.flush()

        membership2 = CompanyMembership(
            user_id=user2.id,
            company_id=company2.id,
            role="system_admin",
            role_id=roles2["system_admin"].id,
        )
        db_session.add(membership2)
        await db_session.flush()
        await db_session.commit()

        return {
            "company2": company2,
            "user2": user2,
            "roles2": roles2,
            "membership2": membership2,
        }

    @pytest.mark.asyncio
    async def test_roles_scoped_to_company(
        self, client: AsyncClient, two_companies: dict
    ) -> None:
        """GET /api/admin/roles only returns roles for the current company."""
        resp = await client.get("/api/admin/roles")
        assert resp.status_code == 200
        data = resp.json()
        # Should only see company 1 roles (client is scoped to company 1)
        for role in data["roles"]:
            # All roles returned should belong to company 1
            assert role["is_system"] is True

    @pytest.mark.asyncio
    async def test_users_scoped_to_company(
        self, client: AsyncClient, two_companies: dict
    ) -> None:
        """GET /api/admin/users only returns users in the current company."""
        resp = await client.get("/api/admin/users")
        assert resp.status_code == 200
        data = resp.json()
        # company2_user should NOT appear in company 1's user list
        usernames = [u["username"] for u in data["users"]]
        assert "company2_user" not in usernames

    @pytest.mark.asyncio
    async def test_role_detail_from_other_company_404(
        self, client: AsyncClient, two_companies: dict
    ) -> None:
        """GET /api/admin/roles/{id} returns 404 for role in another company."""
        # Try to access a role from company 2 via company 1's context
        other_role_id = two_companies["roles2"]["system_admin"].id
        resp = await client.get(f"/api/admin/roles/{other_role_id}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_company2_client_sees_own_roles(
        self, session_factory, two_companies: dict
    ) -> None:
        """A client scoped to company 2 sees company 2's roles only."""

        async def _override_get_db_session():
            async with session_factory() as session:
                try:
                    yield session
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise

        async def _override_get_tenant_context():
            return TenantContext(
                company_id=2,
                company_slug="other-pharma",
                user_id=100,
                membership_role="system_admin",
            )

        app.dependency_overrides[get_db_session] = _override_get_db_session
        app.dependency_overrides[get_tenant_context] = _override_get_tenant_context

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={
                "X-Change-Reason": "Integration test",
                "X-User-Id": "100",
                "X-Company-Id": "2",
            },
        ) as c2:
            resp = await c2.get("/api/admin/roles")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["roles"]) == 5

            # Users list should show company2_user
            resp = await c2.get("/api/admin/users")
            assert resp.status_code == 200
            users_data = resp.json()
            usernames = [u["username"] for u in users_data["users"]]
            assert "company2_user" in usernames
            # admin_user from company 1 should NOT appear
            assert "admin_user" not in usernames

        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Test: Viewer Can Read (users:read is not granted to viewer in RBAC)
# ---------------------------------------------------------------------------


class TestViewerReadAccess:
    """Test that viewer role can read roles (users:read is NOT granted to viewer).

    Per DEFAULT_ROLE_PERMISSIONS, viewer only has read on documents,
    workflows, templates, and training. NOT on users or audit_logs.
    So viewer should get 403 on admin endpoints requiring users:read.
    """

    @pytest.mark.asyncio
    async def test_viewer_cannot_list_users_403(
        self, viewer_client: AsyncClient
    ) -> None:
        """Viewer cannot list users (requires users:read)."""
        resp = await viewer_client.get("/api/admin/users")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_viewer_cannot_list_roles_403(
        self, viewer_client: AsyncClient
    ) -> None:
        """Viewer cannot list roles (requires users:read)."""
        resp = await viewer_client.get("/api/admin/roles")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_viewer_can_list_templates(
        self, viewer_client: AsyncClient
    ) -> None:
        """Viewer CAN list permission templates (requires templates:read)."""
        resp = await viewer_client.get("/api/admin/permission-templates")
        assert resp.status_code == 200
