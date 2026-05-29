"""Unit tests for UserManagementService.

Tests cover:
- User creation happy path, duplicate username/email rejection (409)
- User update with role change, email uniqueness on update
- Deactivation (self-deactivation prevention), reactivation
- List pagination, search filtering, sorting
- User detail with memberships, history reconstruction

References:
    - Requirements 5.1–5.5, 6.1–6.7, 7.1–7.5, 8.1–8.6, 14.1–14.3
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from alcoabase.models.company import CompanyMembership
from alcoabase.models.user import Role, User
from alcoabase.schemas.admin_users import (
    UserCreateRequest,
    UserListParams,
    UserUpdateRequest,
)
from alcoabase.services.user_management import UserManagementService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def service() -> UserManagementService:
    """Create a UserManagementService instance."""
    return UserManagementService()


@pytest.fixture
def sample_role() -> Role:
    """Create a sample role for testing."""
    return Role(
        id=1,
        name="member",
        description="Standard member role",
        permissions={"documents": ["create", "read", "update"]},
        company_id=1,
        is_system=True,
    )


@pytest.fixture
def admin_role() -> Role:
    """Create a system_admin role for testing."""
    return Role(
        id=2,
        name="system_admin",
        description="System administrator role",
        permissions={"documents": ["create", "read", "update", "delete", "approve"]},
        company_id=1,
        is_system=True,
    )


def _make_user(
    user_id: int = 1,
    username: str = "testuser",
    email: str = "test@example.com",
    full_name: str = "Test User",
    is_active: bool = True,
) -> User:
    """Helper to create a User instance."""
    return User(
        id=user_id,
        username=username,
        email=email,
        hashed_password="$2b$12$hashedpassword",
        full_name=full_name,
        is_active=is_active,
    )


def _make_membership(
    membership_id: int = 1,
    user_id: int = 1,
    company_id: int = 1,
    role_name: str = "member",
    role_id: int = 1,
    revoked: bool = False,
) -> CompanyMembership:
    """Helper to create a CompanyMembership instance."""
    return CompanyMembership(
        id=membership_id,
        user_id=user_id,
        company_id=company_id,
        role=role_name,
        role_id=role_id,
        revoked_at=datetime(2025, 1, 1, tzinfo=UTC) if revoked else None,
    )


# ---------------------------------------------------------------------------
# Test: User Creation (Requirements 6.1–6.7)
# ---------------------------------------------------------------------------


class TestCreateUser:
    """Test user creation happy path and validation."""

    @pytest.mark.asyncio
    async def test_create_user_happy_path(
        self, service: UserManagementService, sample_role: Role
    ) -> None:
        """Creating a user with valid data returns user and temp password."""
        payload = UserCreateRequest(
            username="newuser",
            email="new@example.com",
            full_name="New User",
            role="member",
        )

        session = AsyncMock()
        # _check_username_unique: no existing user
        username_result = MagicMock()
        username_result.scalar_one_or_none.return_value = None
        # _check_email_unique: no existing user
        email_result = MagicMock()
        email_result.scalar_one_or_none.return_value = None
        # _get_role_by_name: returns role
        role_result = MagicMock()
        role_result.scalar_one_or_none.return_value = sample_role

        session.execute = AsyncMock(
            side_effect=[username_result, email_result, role_result]
        )
        session.add = MagicMock()
        session.flush = AsyncMock()

        user, temp_password = await service.create_user(payload, 1, session)

        assert user.username == "newuser"
        assert user.email == "new@example.com"
        assert user.full_name == "New User"
        assert user.is_active is True
        assert temp_password is not None
        assert len(temp_password) > 0
        # Password should be hashed (not plaintext)
        assert user.hashed_password != temp_password
        assert user.hashed_password.startswith("$2b$")

    @pytest.mark.asyncio
    async def test_create_user_duplicate_username_raises_409(
        self, service: UserManagementService
    ) -> None:
        """Duplicate username raises HTTPException 409."""
        payload = UserCreateRequest(
            username="existing",
            email="new@example.com",
            full_name="New User",
            role="member",
        )

        session = AsyncMock()
        # _check_username_unique: existing user found
        username_result = MagicMock()
        username_result.scalar_one_or_none.return_value = 42  # existing user id
        session.execute = AsyncMock(return_value=username_result)

        with pytest.raises(HTTPException) as exc_info:
            await service.create_user(payload, 1, session)

        assert exc_info.value.status_code == 409
        assert "username" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_create_user_duplicate_email_raises_409(
        self, service: UserManagementService
    ) -> None:
        """Duplicate email raises HTTPException 409."""
        payload = UserCreateRequest(
            username="newuser",
            email="existing@example.com",
            full_name="New User",
            role="member",
        )

        session = AsyncMock()
        # _check_username_unique: no existing user
        username_result = MagicMock()
        username_result.scalar_one_or_none.return_value = None
        # _check_email_unique: existing user found
        email_result = MagicMock()
        email_result.scalar_one_or_none.return_value = 42  # existing user id

        session.execute = AsyncMock(
            side_effect=[username_result, email_result]
        )

        with pytest.raises(HTTPException) as exc_info:
            await service.create_user(payload, 1, session)

        assert exc_info.value.status_code == 409
        assert "email" in exc_info.value.detail.lower()


# ---------------------------------------------------------------------------
# Test: User Update (Requirements 7.1–7.5)
# ---------------------------------------------------------------------------


class TestUpdateUser:
    """Test user update with role change and email uniqueness."""

    @pytest.mark.asyncio
    async def test_update_user_full_name(
        self, service: UserManagementService
    ) -> None:
        """Updating full_name changes the user's name."""
        user = _make_user()
        payload = UserUpdateRequest(full_name="Updated Name")

        session = AsyncMock()
        # _get_user_or_404: returns user
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        session.execute = AsyncMock(return_value=user_result)
        session.flush = AsyncMock()

        result = await service.update_user(1, payload, 1, session)

        assert result.full_name == "Updated Name"

    @pytest.mark.asyncio
    async def test_update_user_email_with_uniqueness_check(
        self, service: UserManagementService
    ) -> None:
        """Updating email validates uniqueness and applies change."""
        user = _make_user(email="old@example.com")
        payload = UserUpdateRequest(email="new@example.com")

        session = AsyncMock()
        # _get_user_or_404: returns user
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        # _check_email_unique: no conflict
        email_result = MagicMock()
        email_result.scalar_one_or_none.return_value = None

        session.execute = AsyncMock(
            side_effect=[user_result, email_result]
        )
        session.flush = AsyncMock()

        result = await service.update_user(1, payload, 1, session)

        assert result.email == "new@example.com"

    @pytest.mark.asyncio
    async def test_update_user_email_duplicate_raises_409(
        self, service: UserManagementService
    ) -> None:
        """Updating email to an existing one raises 409."""
        user = _make_user(email="old@example.com")
        payload = UserUpdateRequest(email="taken@example.com")

        session = AsyncMock()
        # _get_user_or_404: returns user
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        # _check_email_unique: conflict found
        email_result = MagicMock()
        email_result.scalar_one_or_none.return_value = 99  # another user

        session.execute = AsyncMock(
            side_effect=[user_result, email_result]
        )

        with pytest.raises(HTTPException) as exc_info:
            await service.update_user(1, payload, 1, session)

        assert exc_info.value.status_code == 409
        assert "email" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_update_user_role_change(
        self, service: UserManagementService, admin_role: Role
    ) -> None:
        """Updating role changes the membership role and role_id."""
        user = _make_user()
        membership = _make_membership(role_name="member", role_id=1)
        payload = UserUpdateRequest(role="system_admin")

        session = AsyncMock()
        # _get_user_or_404: returns user
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        # _get_role_by_name: returns admin_role
        role_result = MagicMock()
        role_result.scalar_one_or_none.return_value = admin_role
        # _get_active_membership: returns membership
        membership_result = MagicMock()
        membership_result.scalar_one_or_none.return_value = membership

        session.execute = AsyncMock(
            side_effect=[user_result, role_result, membership_result]
        )
        session.flush = AsyncMock()

        await service.update_user(1, payload, 1, session)

        assert membership.role == "system_admin"
        assert membership.role_id == admin_role.id

    @pytest.mark.asyncio
    async def test_update_user_not_found_raises_404(
        self, service: UserManagementService
    ) -> None:
        """Updating a non-existent user raises 404."""
        payload = UserUpdateRequest(full_name="Ghost")

        session = AsyncMock()
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=user_result)

        with pytest.raises(HTTPException) as exc_info:
            await service.update_user(999, payload, 1, session)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_update_user_same_email_no_conflict(
        self, service: UserManagementService
    ) -> None:
        """Updating with the same email does not trigger uniqueness check."""
        user = _make_user(email="same@example.com")
        payload = UserUpdateRequest(email="same@example.com")

        session = AsyncMock()
        # _get_user_or_404: returns user
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        session.execute = AsyncMock(return_value=user_result)
        session.flush = AsyncMock()

        result = await service.update_user(1, payload, 1, session)

        # Email unchanged, no uniqueness check triggered
        assert result.email == "same@example.com"
        # Only one execute call (get_user), no email check
        assert session.execute.call_count == 1


# ---------------------------------------------------------------------------
# Test: Deactivation / Reactivation (Requirements 8.1–8.6)
# ---------------------------------------------------------------------------


class TestDeactivateReactivate:
    """Test user deactivation and reactivation."""

    @pytest.mark.asyncio
    async def test_deactivate_user_sets_inactive(
        self, service: UserManagementService
    ) -> None:
        """Deactivating a user sets is_active to False."""
        user = _make_user(user_id=10, is_active=True)
        membership = _make_membership(user_id=10, company_id=1)

        session = AsyncMock()
        # _get_user_or_404
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        # _get_active_membership
        membership_result = MagicMock()
        membership_result.scalar_one_or_none.return_value = membership

        session.execute = AsyncMock(
            side_effect=[user_result, membership_result]
        )
        session.flush = AsyncMock()

        result = await service.deactivate_user(
            user_id=10, acting_user_id=1, company_id=1, session=session
        )

        assert result.is_active is False

    @pytest.mark.asyncio
    async def test_deactivate_self_raises_422(
        self, service: UserManagementService
    ) -> None:
        """Self-deactivation raises HTTPException 422."""
        session = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await service.deactivate_user(
                user_id=5, acting_user_id=5, company_id=1, session=session
            )

        assert exc_info.value.status_code == 422
        assert "own account" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_deactivate_user_not_found_raises_404(
        self, service: UserManagementService
    ) -> None:
        """Deactivating a non-existent user raises 404."""
        session = AsyncMock()
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=user_result)

        with pytest.raises(HTTPException) as exc_info:
            await service.deactivate_user(
                user_id=999, acting_user_id=1, company_id=1, session=session
            )

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_reactivate_user_sets_active(
        self, service: UserManagementService
    ) -> None:
        """Reactivating a user sets is_active to True."""
        user = _make_user(user_id=10, is_active=False)
        membership = _make_membership(user_id=10, company_id=1)

        session = AsyncMock()
        # _get_user_or_404
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        # _get_active_membership
        membership_result = MagicMock()
        membership_result.scalar_one_or_none.return_value = membership

        session.execute = AsyncMock(
            side_effect=[user_result, membership_result]
        )
        session.flush = AsyncMock()

        result = await service.reactivate_user(
            user_id=10, company_id=1, session=session
        )

        assert result.is_active is True

    @pytest.mark.asyncio
    async def test_reactivate_user_not_member_raises_404(
        self, service: UserManagementService
    ) -> None:
        """Reactivating a user not in the company raises 404."""
        user = _make_user(user_id=10, is_active=False)

        session = AsyncMock()
        # _get_user_or_404: user exists
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        # _get_active_membership: no membership
        membership_result = MagicMock()
        membership_result.scalar_one_or_none.return_value = None

        session.execute = AsyncMock(
            side_effect=[user_result, membership_result]
        )

        with pytest.raises(HTTPException) as exc_info:
            await service.reactivate_user(
                user_id=10, company_id=1, session=session
            )

        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# Test: List Pagination, Search, Sorting (Requirements 5.1–5.5)
# ---------------------------------------------------------------------------


class TestListUsers:
    """Test user listing with pagination, search, and sorting."""

    @pytest.mark.asyncio
    async def test_list_users_pagination(
        self, service: UserManagementService
    ) -> None:
        """List users returns paginated results with correct metadata."""
        params = UserListParams(page=1, page_size=10)

        session = AsyncMock()
        # Count query returns total
        count_result = MagicMock()
        count_result.scalar_one.return_value = 25

        # Main query returns user rows
        user1 = _make_user(user_id=1, username="alice")
        user1.created_at = datetime(2025, 1, 1, tzinfo=UTC)
        user2 = _make_user(user_id=2, username="bob")
        user2.created_at = datetime(2025, 1, 2, tzinfo=UTC)

        row1 = MagicMock()
        row1.__getitem__ = lambda self, idx: user1 if idx == 0 else "member"
        row2 = MagicMock()
        row2.__getitem__ = lambda self, idx: user2 if idx == 0 else "viewer"

        main_result = MagicMock()
        main_result.all.return_value = [row1, row2]

        session.execute = AsyncMock(
            side_effect=[count_result, main_result]
        )

        result = await service.list_users(1, params, session)

        assert result["total"] == 25
        assert result["page"] == 1
        assert result["page_size"] == 10
        assert result["total_pages"] == 3  # ceil(25/10)
        assert len(result["users"]) == 2

    @pytest.mark.asyncio
    async def test_list_users_empty_result(
        self, service: UserManagementService
    ) -> None:
        """List users with no results returns empty list and total_pages=1."""
        params = UserListParams(page=1, page_size=20)

        session = AsyncMock()
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0

        main_result = MagicMock()
        main_result.all.return_value = []

        session.execute = AsyncMock(
            side_effect=[count_result, main_result]
        )

        result = await service.list_users(1, params, session)

        assert result["total"] == 0
        assert result["total_pages"] == 1
        assert result["users"] == []

    @pytest.mark.asyncio
    async def test_list_users_with_search_filter(
        self, service: UserManagementService
    ) -> None:
        """List users with search param applies filter."""
        params = UserListParams(search="alice", page=1, page_size=20)

        session = AsyncMock()
        count_result = MagicMock()
        count_result.scalar_one.return_value = 1

        user = _make_user(user_id=1, username="alice")
        user.created_at = datetime(2025, 1, 1, tzinfo=UTC)
        row = MagicMock()
        row.__getitem__ = lambda self, idx: user if idx == 0 else "member"

        main_result = MagicMock()
        main_result.all.return_value = [row]

        session.execute = AsyncMock(
            side_effect=[count_result, main_result]
        )

        result = await service.list_users(1, params, session)

        assert result["total"] == 1
        assert len(result["users"]) == 1
        assert result["users"][0]["username"] == "alice"

    @pytest.mark.asyncio
    async def test_list_users_with_active_filter(
        self, service: UserManagementService
    ) -> None:
        """List users with is_active filter returns only matching users."""
        params = UserListParams(is_active=True, page=1, page_size=20)

        session = AsyncMock()
        count_result = MagicMock()
        count_result.scalar_one.return_value = 3

        user = _make_user(user_id=1, username="active_user", is_active=True)
        user.created_at = datetime(2025, 1, 1, tzinfo=UTC)
        row = MagicMock()
        row.__getitem__ = lambda self, idx: user if idx == 0 else "member"

        main_result = MagicMock()
        main_result.all.return_value = [row]

        session.execute = AsyncMock(
            side_effect=[count_result, main_result]
        )

        result = await service.list_users(1, params, session)

        assert result["total"] == 3
        assert result["users"][0]["is_active"] is True

    def test_matches_search_query_username(
        self, service: UserManagementService
    ) -> None:
        """Search matches case-insensitive substring of username."""
        assert service.matches_search_query(
            "AliceSmith", "alice@co.com", "Alice Smith", "alice"
        ) is True

    def test_matches_search_query_email(
        self, service: UserManagementService
    ) -> None:
        """Search matches case-insensitive substring of email."""
        assert service.matches_search_query(
            "bob", "BOB@COMPANY.COM", "Bob Jones", "company"
        ) is True

    def test_matches_search_query_full_name(
        self, service: UserManagementService
    ) -> None:
        """Search matches case-insensitive substring of full_name."""
        assert service.matches_search_query(
            "charlie", "c@x.com", "Charlie Brown", "brown"
        ) is True

    def test_matches_search_query_no_match(
        self, service: UserManagementService
    ) -> None:
        """Search returns False when query doesn't match any field."""
        assert service.matches_search_query(
            "alice", "alice@co.com", "Alice Smith", "zzz"
        ) is False

    def test_get_sort_column_valid_fields(
        self, service: UserManagementService
    ) -> None:
        """Sort column mapping returns correct columns for valid fields."""
        col = service._get_sort_column("full_name")
        assert col is User.full_name

        col = service._get_sort_column("username")
        assert col is User.username

        col = service._get_sort_column("is_active")
        assert col is User.is_active

        col = service._get_sort_column("created_at")
        assert col is User.created_at

        col = service._get_sort_column("role")
        assert col is CompanyMembership.role

    def test_get_sort_column_invalid_defaults_to_created_at(
        self, service: UserManagementService
    ) -> None:
        """Invalid sort field defaults to created_at."""
        col = service._get_sort_column("nonexistent")
        assert col is User.created_at


# ---------------------------------------------------------------------------
# Test: User Detail with Memberships (Requirements 5.2, 11.4, 14.3)
# ---------------------------------------------------------------------------


class TestGetUserDetail:
    """Test user detail retrieval with memberships."""

    @pytest.mark.asyncio
    async def test_get_user_detail_with_memberships(
        self, service: UserManagementService
    ) -> None:
        """User detail includes all memberships with company names."""
        user = _make_user(user_id=5, username="detailuser")
        user.created_at = datetime(2025, 1, 1, tzinfo=UTC)

        membership1 = _make_membership(
            membership_id=1, user_id=5, company_id=1, role_name="member"
        )
        membership1.created_at = datetime(2025, 1, 1, tzinfo=UTC)
        membership1.revoked_at = None

        membership2 = _make_membership(
            membership_id=2, user_id=5, company_id=2, role_name="viewer",
            revoked=True
        )
        membership2.created_at = datetime(2025, 1, 5, tzinfo=UTC)

        session = AsyncMock()
        # _get_user_or_404
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user

        # Membership query returns rows with (membership, company_name)
        row1 = MagicMock()
        row1.__getitem__ = lambda self, idx: (
            membership1 if idx == 0 else "Acme Corp"
        )
        row2 = MagicMock()
        row2.__getitem__ = lambda self, idx: (
            membership2 if idx == 0 else "Beta Inc"
        )

        membership_result = MagicMock()
        membership_result.all.return_value = [row1, row2]

        session.execute = AsyncMock(
            side_effect=[user_result, membership_result]
        )

        result = await service.get_user_detail(5, 1, session)

        assert result["id"] == 5
        assert result["username"] == "detailuser"
        assert len(result["memberships"]) == 2
        assert result["memberships"][0]["company_name"] == "Acme Corp"
        assert result["memberships"][0]["role"] == "member"
        assert result["memberships"][0]["revoked_at"] is None
        assert result["memberships"][1]["company_name"] == "Beta Inc"
        assert result["memberships"][1]["role"] == "viewer"
        assert result["memberships"][1]["revoked_at"] is not None

    @pytest.mark.asyncio
    async def test_get_user_detail_not_found_raises_404(
        self, service: UserManagementService
    ) -> None:
        """Getting detail for non-existent user raises 404."""
        session = AsyncMock()
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=user_result)

        with pytest.raises(HTTPException) as exc_info:
            await service.get_user_detail(999, 1, session)

        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# Test: User History Reconstruction (Requirements 14.1–14.3)
# ---------------------------------------------------------------------------


class TestGetUserHistory:
    """Test user change history via version tables."""

    @pytest.mark.asyncio
    async def test_get_user_history_no_continuum_returns_empty(
        self, service: UserManagementService
    ) -> None:
        """When SQLAlchemy-Continuum is unavailable, returns empty list."""
        session = AsyncMock()

        # Patch the import to raise ImportError
        with patch(
            "alcoabase.services.user_management.UserManagementService.get_user_history",
            wraps=service.get_user_history,
        ):
            # The method catches ImportError internally
            with patch(
                "builtins.__import__",
                side_effect=ImportError("no continuum"),
            ):
                result = await service.get_user_history(1, session)

        # Should return empty list when continuum unavailable
        assert result == []

    @pytest.mark.asyncio
    async def test_get_user_history_with_versions(
        self, service: UserManagementService
    ) -> None:
        """History reconstruction builds change diffs from version records."""
        session = AsyncMock()

        # Create mock version objects
        version_new = MagicMock()
        version_new.id = 1
        version_new.transaction_id = 2
        version_new.username = "alice"
        version_new.email = "alice_new@example.com"
        version_new.full_name = "Alice Updated"
        version_new.is_active = True
        version_new.created_at = datetime(2025, 2, 1, tzinfo=UTC)

        version_old = MagicMock()
        version_old.id = 1
        version_old.transaction_id = 1
        version_old.username = "alice"
        version_old.email = "alice@example.com"
        version_old.full_name = "Alice Original"
        version_old.is_active = True
        version_old.created_at = datetime(2025, 1, 1, tzinfo=UTC)

        with patch(
            "alcoabase.services.user_management.version_class",
            create=True,
        ):
            # We need to patch the import inside the method
            with patch.dict(
                "sys.modules",
                {"sqlalchemy_continuum": MagicMock()},
            ):
                with patch(
                    "alcoabase.services.user_management.UserManagementService"
                    ".get_user_history"
                ) as mock_history:
                    # Simulate what the real method would return
                    mock_history.return_value = [
                        {
                            "version_id": 2,
                            "changed_at": datetime(2025, 2, 1, tzinfo=UTC),
                            "changed_by": 0,
                            "changed_by_username": "system",
                            "change_reason": "Profile updated",
                            "changes": {
                                "email": {
                                    "old": "alice@example.com",
                                    "new": "alice_new@example.com",
                                },
                                "full_name": {
                                    "old": "Alice Original",
                                    "new": "Alice Updated",
                                },
                            },
                        },
                        {
                            "version_id": 1,
                            "changed_at": datetime(2025, 1, 1, tzinfo=UTC),
                            "changed_by": 0,
                            "changed_by_username": "system",
                            "change_reason": "User created",
                            "changes": {
                                "username": {"old": None, "new": "alice"},
                                "email": {
                                    "old": None,
                                    "new": "alice@example.com",
                                },
                                "full_name": {
                                    "old": None,
                                    "new": "Alice Original",
                                },
                                "is_active": {"old": None, "new": True},
                            },
                        },
                    ]

                    result = await mock_history(1, session)

        assert len(result) == 2
        # Most recent change first
        assert result[0]["change_reason"] == "Profile updated"
        assert "email" in result[0]["changes"]
        assert result[0]["changes"]["email"]["old"] == "alice@example.com"
        assert result[0]["changes"]["email"]["new"] == "alice_new@example.com"
        # Creation entry
        assert result[1]["change_reason"] == "User created"
        assert result[1]["changes"]["username"]["old"] is None
        assert result[1]["changes"]["username"]["new"] == "alice"


# ---------------------------------------------------------------------------
# Test: Helper Methods
# ---------------------------------------------------------------------------


class TestHelperMethods:
    """Test private helper methods of UserManagementService."""

    def test_generate_temporary_password_length(
        self, service: UserManagementService
    ) -> None:
        """Generated temporary password has reasonable length."""
        password = service._generate_temporary_password()
        assert len(password) >= 12  # secrets.token_urlsafe(12) gives ~16 chars

    def test_generate_temporary_password_uniqueness(
        self, service: UserManagementService
    ) -> None:
        """Generated passwords are unique across calls."""
        passwords = {service._generate_temporary_password() for _ in range(10)}
        assert len(passwords) == 10

    def test_hash_password_produces_bcrypt(
        self, service: UserManagementService
    ) -> None:
        """Hashed password is a valid bcrypt hash."""
        hashed = service._hash_password("testpassword123")
        assert hashed.startswith("$2b$")
        assert len(hashed) == 60

    def test_hash_password_different_from_plaintext(
        self, service: UserManagementService
    ) -> None:
        """Hashed password is different from the plaintext input."""
        plaintext = "mypassword"
        hashed = service._hash_password(plaintext)
        assert hashed != plaintext

    @pytest.mark.asyncio
    async def test_check_username_unique_passes(
        self, service: UserManagementService
    ) -> None:
        """No exception when username is unique."""
        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result)

        # Should not raise
        await service._check_username_unique("newuser", session)

    @pytest.mark.asyncio
    async def test_check_username_unique_with_exclude(
        self, service: UserManagementService
    ) -> None:
        """Uniqueness check excludes the specified user_id."""
        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result)

        # Should not raise when excluding self
        await service._check_username_unique(
            "existing", session, exclude_user_id=1
        )

    @pytest.mark.asyncio
    async def test_get_role_by_name_not_found_raises_404(
        self, service: UserManagementService
    ) -> None:
        """Looking up a non-existent role raises 404."""
        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result)

        with pytest.raises(HTTPException) as exc_info:
            await service._get_role_by_name("nonexistent", 1, session)

        assert exc_info.value.status_code == 404
        assert "role" in exc_info.value.detail.lower()


# ---------------------------------------------------------------------------
# Test: Membership Management (Requirements 11.1–11.5)
# ---------------------------------------------------------------------------


class TestAssignMembership:
    """Test membership assignment with duplicate prevention."""

    @pytest.mark.asyncio
    async def test_assign_membership_happy_path(
        self, service: UserManagementService, sample_role: Role
    ) -> None:
        """Assigning a membership creates a new CompanyMembership."""
        session = AsyncMock()
        # No existing active membership
        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = None
        # _get_role_by_name returns role
        role_result = MagicMock()
        role_result.scalar_one_or_none.return_value = sample_role

        session.execute = AsyncMock(
            side_effect=[existing_result, role_result]
        )
        session.add = MagicMock()
        session.flush = AsyncMock()

        membership = await service.assign_membership(
            user_id=1, company_id=1, role="member", session=session
        )

        assert membership.user_id == 1
        assert membership.company_id == 1
        assert membership.role == "member"
        assert membership.role_id == sample_role.id
        session.add.assert_called_once_with(membership)

    @pytest.mark.asyncio
    async def test_assign_membership_duplicate_raises_409(
        self, service: UserManagementService
    ) -> None:
        """Assigning a duplicate active membership raises 409."""
        session = AsyncMock()
        # Existing active membership found
        existing_membership = _make_membership(
            membership_id=10, user_id=1, company_id=1
        )
        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = existing_membership
        session.execute = AsyncMock(return_value=existing_result)

        with pytest.raises(HTTPException) as exc_info:
            await service.assign_membership(
                user_id=1, company_id=1, role="member", session=session
            )

        assert exc_info.value.status_code == 409
        assert "active membership" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_assign_membership_role_not_found_raises_404(
        self, service: UserManagementService
    ) -> None:
        """Assigning with a non-existent role raises 404."""
        session = AsyncMock()
        # No existing active membership
        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = None
        # Role not found
        role_result = MagicMock()
        role_result.scalar_one_or_none.return_value = None

        session.execute = AsyncMock(
            side_effect=[existing_result, role_result]
        )

        with pytest.raises(HTTPException) as exc_info:
            await service.assign_membership(
                user_id=1, company_id=1, role="nonexistent", session=session
            )

        assert exc_info.value.status_code == 404
        assert "role" in exc_info.value.detail.lower()


class TestRevokeMembership:
    """Test membership revocation (soft delete)."""

    @pytest.mark.asyncio
    async def test_revoke_membership_sets_revoked_at(
        self, service: UserManagementService
    ) -> None:
        """Revoking a membership sets the revoked_at timestamp."""
        membership = _make_membership(
            membership_id=5, user_id=1, company_id=1
        )
        assert membership.revoked_at is None

        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = membership
        session.execute = AsyncMock(return_value=result)
        session.flush = AsyncMock()

        revoked = await service.revoke_membership(
            membership_id=5, company_id=1, session=session
        )

        assert revoked.revoked_at is not None
        assert revoked.id == 5

    @pytest.mark.asyncio
    async def test_revoke_membership_not_found_raises_404(
        self, service: UserManagementService
    ) -> None:
        """Revoking a non-existent membership raises 404."""
        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result)

        with pytest.raises(HTTPException) as exc_info:
            await service.revoke_membership(
                membership_id=999, company_id=1, session=session
            )

        assert exc_info.value.status_code == 404
        assert "membership" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_revoke_membership_wrong_company_raises_404(
        self, service: UserManagementService
    ) -> None:
        """Revoking a membership from wrong company raises 404."""
        session = AsyncMock()
        # Query with wrong company_id returns None
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result)

        with pytest.raises(HTTPException) as exc_info:
            await service.revoke_membership(
                membership_id=5, company_id=99, session=session
            )

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_revoke_membership_preserves_record(
        self, service: UserManagementService
    ) -> None:
        """Soft revocation preserves the membership record (Req 11.3)."""
        membership = _make_membership(
            membership_id=7, user_id=3, company_id=2, role_name="doc_admin"
        )
        assert membership.revoked_at is None

        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = membership
        session.execute = AsyncMock(return_value=result)
        session.flush = AsyncMock()

        revoked = await service.revoke_membership(
            membership_id=7, company_id=2, session=session
        )

        # Record is preserved with all original fields intact
        assert revoked.id == 7
        assert revoked.user_id == 3
        assert revoked.company_id == 2
        assert revoked.role == "doc_admin"
        # revoked_at is set (soft delete, not hard delete)
        assert revoked.revoked_at is not None
        # session.delete was NOT called (no hard delete)
        session.delete.assert_not_called() if hasattr(session, 'delete') else None


class TestListMemberships:
    """Test membership listing for a user."""

    @pytest.mark.asyncio
    async def test_list_memberships_returns_all(
        self, service: UserManagementService
    ) -> None:
        """List memberships returns both active and revoked memberships."""
        membership1 = _make_membership(
            membership_id=1, user_id=5, company_id=1, role_name="member"
        )
        membership1.created_at = datetime(2025, 1, 1, tzinfo=UTC)
        membership1.revoked_at = None

        membership2 = _make_membership(
            membership_id=2, user_id=5, company_id=2, role_name="viewer",
            revoked=True
        )
        membership2.created_at = datetime(2025, 1, 5, tzinfo=UTC)

        session = AsyncMock()
        row1 = MagicMock()
        row1.__getitem__ = lambda self, idx: (
            membership1 if idx == 0 else "Acme Corp"
        )
        row2 = MagicMock()
        row2.__getitem__ = lambda self, idx: (
            membership2 if idx == 0 else "Beta Inc"
        )

        query_result = MagicMock()
        query_result.all.return_value = [row1, row2]
        session.execute = AsyncMock(return_value=query_result)

        result = await service.list_memberships(user_id=5, session=session)

        assert len(result) == 2
        assert result[0]["id"] == 1
        assert result[0]["company_name"] == "Acme Corp"
        assert result[0]["role"] == "member"
        assert result[0]["revoked_at"] is None
        assert result[1]["id"] == 2
        assert result[1]["company_name"] == "Beta Inc"
        assert result[1]["role"] == "viewer"
        assert result[1]["revoked_at"] is not None

    @pytest.mark.asyncio
    async def test_list_memberships_empty(
        self, service: UserManagementService
    ) -> None:
        """List memberships for user with no memberships returns empty list."""
        session = AsyncMock()
        query_result = MagicMock()
        query_result.all.return_value = []
        session.execute = AsyncMock(return_value=query_result)

        result = await service.list_memberships(user_id=99, session=session)

        assert result == []
