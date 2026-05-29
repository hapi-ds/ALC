"""Unit tests for admin Pydantic request/response schemas.

Tests validation rules for UserCreateRequest, UserUpdateRequest,
UserListParams, PermissionTemplateCreateRequest, and related schemas.

References:
    - Requirements 5.1: User listing and search
    - Requirements 6.1, 6.2, 6.3: User creation validation
"""

import pytest
from pydantic import ValidationError

from alcoabase.schemas.admin_users import (
    UserCreateRequest,
    UserListParams,
    UserUpdateRequest,
)
from alcoabase.schemas.admin_permission_templates import (
    PermissionTemplateCreateRequest,
    PermissionTemplateUpdateRequest,
    RoleActionMapping,
)
from alcoabase.schemas.admin_memberships import AssignMembershipRequest
from alcoabase.schemas.admin_roles import PermissionEntry


# ---------------------------------------------------------------------------
# UserCreateRequest Tests
# ---------------------------------------------------------------------------


class TestUserCreateRequest:
    """Tests for UserCreateRequest validation."""

    def test_valid_full_request(self) -> None:
        req = UserCreateRequest(
            username="john.doe",
            email="john@example.com",
            full_name="John Doe",
            role="member",
        )
        assert req.username == "john.doe"
        assert req.email == "john@example.com"
        assert req.full_name == "John Doe"
        assert req.role == "member"

    def test_valid_username_alphanumeric(self) -> None:
        req = UserCreateRequest(
            username="user123",
            email="u@example.com",
            full_name="User",
            role="viewer",
        )
        assert req.username == "user123"

    def test_valid_username_with_dots(self) -> None:
        req = UserCreateRequest(
            username="first.last",
            email="u@example.com",
            full_name="User",
            role="viewer",
        )
        assert req.username == "first.last"

    def test_valid_username_with_hyphens(self) -> None:
        req = UserCreateRequest(
            username="first-last",
            email="u@example.com",
            full_name="User",
            role="viewer",
        )
        assert req.username == "first-last"

    def test_valid_username_with_underscores(self) -> None:
        req = UserCreateRequest(
            username="first_last",
            email="u@example.com",
            full_name="User",
            role="viewer",
        )
        assert req.username == "first_last"

    def test_username_min_length_3(self) -> None:
        req = UserCreateRequest(
            username="abc",
            email="u@example.com",
            full_name="User",
            role="viewer",
        )
        assert req.username == "abc"

    def test_username_too_short_rejected(self) -> None:
        with pytest.raises(ValidationError):
            UserCreateRequest(
                username="ab",
                email="u@example.com",
                full_name="User",
                role="viewer",
            )

    def test_username_max_length_100(self) -> None:
        req = UserCreateRequest(
            username="a" * 100,
            email="u@example.com",
            full_name="User",
            role="viewer",
        )
        assert len(req.username) == 100

    def test_username_exceeds_100_rejected(self) -> None:
        with pytest.raises(ValidationError):
            UserCreateRequest(
                username="a" * 101,
                email="u@example.com",
                full_name="User",
                role="viewer",
            )

    def test_username_with_spaces_rejected(self) -> None:
        with pytest.raises(ValidationError):
            UserCreateRequest(
                username="john doe",
                email="u@example.com",
                full_name="User",
                role="viewer",
            )

    def test_username_with_special_chars_rejected(self) -> None:
        with pytest.raises(ValidationError):
            UserCreateRequest(
                username="john@doe",
                email="u@example.com",
                full_name="User",
                role="viewer",
            )

    def test_username_with_unicode_rejected(self) -> None:
        with pytest.raises(ValidationError):
            UserCreateRequest(
                username="jöhn",
                email="u@example.com",
                full_name="User",
                role="viewer",
            )

    def test_invalid_email_rejected(self) -> None:
        with pytest.raises(ValidationError):
            UserCreateRequest(
                username="john",
                email="not-an-email",
                full_name="User",
                role="viewer",
            )

    def test_email_without_domain_rejected(self) -> None:
        with pytest.raises(ValidationError):
            UserCreateRequest(
                username="john",
                email="john@",
                full_name="User",
                role="viewer",
            )

    def test_full_name_min_length_1(self) -> None:
        req = UserCreateRequest(
            username="john",
            email="u@example.com",
            full_name="J",
            role="viewer",
        )
        assert req.full_name == "J"

    def test_full_name_empty_rejected(self) -> None:
        with pytest.raises(ValidationError):
            UserCreateRequest(
                username="john",
                email="u@example.com",
                full_name="",
                role="viewer",
            )

    def test_full_name_max_length_200(self) -> None:
        req = UserCreateRequest(
            username="john",
            email="u@example.com",
            full_name="A" * 200,
            role="viewer",
        )
        assert len(req.full_name) == 200

    def test_full_name_exceeds_200_rejected(self) -> None:
        with pytest.raises(ValidationError):
            UserCreateRequest(
                username="john",
                email="u@example.com",
                full_name="A" * 201,
                role="viewer",
            )

    def test_valid_role_system_admin(self) -> None:
        req = UserCreateRequest(
            username="admin",
            email="a@example.com",
            full_name="Admin",
            role="system_admin",
        )
        assert req.role == "system_admin"

    def test_valid_role_doc_admin(self) -> None:
        req = UserCreateRequest(
            username="admin",
            email="a@example.com",
            full_name="Admin",
            role="doc_admin",
        )
        assert req.role == "doc_admin"

    def test_valid_role_it_admin(self) -> None:
        req = UserCreateRequest(
            username="admin",
            email="a@example.com",
            full_name="Admin",
            role="it_admin",
        )
        assert req.role == "it_admin"

    def test_valid_role_member(self) -> None:
        req = UserCreateRequest(
            username="user1",
            email="a@example.com",
            full_name="User",
            role="member",
        )
        assert req.role == "member"

    def test_valid_role_viewer(self) -> None:
        req = UserCreateRequest(
            username="user1",
            email="a@example.com",
            full_name="User",
            role="viewer",
        )
        assert req.role == "viewer"

    def test_invalid_role_rejected(self) -> None:
        with pytest.raises(ValidationError):
            UserCreateRequest(
                username="user1",
                email="a@example.com",
                full_name="User",
                role="superadmin",  # type: ignore[arg-type]
            )

    def test_empty_role_rejected(self) -> None:
        with pytest.raises(ValidationError):
            UserCreateRequest(
                username="user1",
                email="a@example.com",
                full_name="User",
                role="",  # type: ignore[arg-type]
            )

    def test_missing_required_fields_rejected(self) -> None:
        with pytest.raises(ValidationError):
            UserCreateRequest()  # type: ignore[call-arg]

    def test_serialization_round_trip(self) -> None:
        req = UserCreateRequest(
            username="john.doe",
            email="john@example.com",
            full_name="John Doe",
            role="member",
        )
        data = req.model_dump()
        restored = UserCreateRequest(**data)
        assert restored == req

    def test_json_serialization(self) -> None:
        req = UserCreateRequest(
            username="john.doe",
            email="john@example.com",
            full_name="John Doe",
            role="member",
        )
        json_str = req.model_dump_json()
        restored = UserCreateRequest.model_validate_json(json_str)
        assert restored == req


# ---------------------------------------------------------------------------
# UserUpdateRequest Tests
# ---------------------------------------------------------------------------


class TestUserUpdateRequest:
    """Tests for UserUpdateRequest validation."""

    def test_all_fields_optional(self) -> None:
        req = UserUpdateRequest()
        assert req.full_name is None
        assert req.email is None
        assert req.role is None

    def test_update_full_name_only(self) -> None:
        req = UserUpdateRequest(full_name="New Name")
        assert req.full_name == "New Name"
        assert req.email is None
        assert req.role is None

    def test_update_email_only(self) -> None:
        req = UserUpdateRequest(email="new@example.com")
        assert req.email == "new@example.com"
        assert req.full_name is None
        assert req.role is None

    def test_update_role_only(self) -> None:
        req = UserUpdateRequest(role="doc_admin")
        assert req.role == "doc_admin"
        assert req.full_name is None
        assert req.email is None

    def test_update_all_fields(self) -> None:
        req = UserUpdateRequest(
            full_name="Updated Name",
            email="updated@example.com",
            role="it_admin",
        )
        assert req.full_name == "Updated Name"
        assert req.email == "updated@example.com"
        assert req.role == "it_admin"

    def test_full_name_empty_rejected(self) -> None:
        with pytest.raises(ValidationError):
            UserUpdateRequest(full_name="")

    def test_full_name_exceeds_200_rejected(self) -> None:
        with pytest.raises(ValidationError):
            UserUpdateRequest(full_name="A" * 201)

    def test_invalid_email_rejected(self) -> None:
        with pytest.raises(ValidationError):
            UserUpdateRequest(email="not-valid")

    def test_invalid_role_rejected(self) -> None:
        with pytest.raises(ValidationError):
            UserUpdateRequest(role="admin")  # type: ignore[arg-type]

    def test_serialization_round_trip(self) -> None:
        req = UserUpdateRequest(full_name="Test", email="t@example.com", role="viewer")
        data = req.model_dump()
        restored = UserUpdateRequest(**data)
        assert restored == req

    def test_json_excludes_none_fields(self) -> None:
        req = UserUpdateRequest(full_name="Only Name")
        data = req.model_dump(exclude_none=True)
        assert "email" not in data
        assert "role" not in data
        assert data["full_name"] == "Only Name"


# ---------------------------------------------------------------------------
# UserListParams Tests
# ---------------------------------------------------------------------------


class TestUserListParams:
    """Tests for UserListParams validation."""

    def test_defaults(self) -> None:
        params = UserListParams()
        assert params.search is None
        assert params.sort_by == "created_at"
        assert params.sort_dir == "desc"
        assert params.page == 1
        assert params.page_size == 20
        assert params.is_active is None

    def test_custom_search(self) -> None:
        params = UserListParams(search="john")
        assert params.search == "john"

    def test_search_max_length_200(self) -> None:
        params = UserListParams(search="x" * 200)
        assert len(params.search) == 200  # type: ignore[arg-type]

    def test_search_exceeds_200_rejected(self) -> None:
        with pytest.raises(ValidationError):
            UserListParams(search="x" * 201)

    def test_valid_sort_by_fields(self) -> None:
        for field in ["full_name", "username", "role", "is_active", "created_at"]:
            params = UserListParams(sort_by=field)  # type: ignore[arg-type]
            assert params.sort_by == field

    def test_invalid_sort_by_rejected(self) -> None:
        with pytest.raises(ValidationError):
            UserListParams(sort_by="email")  # type: ignore[arg-type]

    def test_sort_dir_asc(self) -> None:
        params = UserListParams(sort_dir="asc")
        assert params.sort_dir == "asc"

    def test_sort_dir_desc(self) -> None:
        params = UserListParams(sort_dir="desc")
        assert params.sort_dir == "desc"

    def test_invalid_sort_dir_rejected(self) -> None:
        with pytest.raises(ValidationError):
            UserListParams(sort_dir="ascending")  # type: ignore[arg-type]

    def test_page_minimum_1(self) -> None:
        params = UserListParams(page=1)
        assert params.page == 1

    def test_page_zero_rejected(self) -> None:
        with pytest.raises(ValidationError):
            UserListParams(page=0)

    def test_page_negative_rejected(self) -> None:
        with pytest.raises(ValidationError):
            UserListParams(page=-1)

    def test_page_size_minimum_1(self) -> None:
        params = UserListParams(page_size=1)
        assert params.page_size == 1

    def test_page_size_maximum_100(self) -> None:
        params = UserListParams(page_size=100)
        assert params.page_size == 100

    def test_page_size_zero_rejected(self) -> None:
        with pytest.raises(ValidationError):
            UserListParams(page_size=0)

    def test_page_size_exceeds_100_rejected(self) -> None:
        with pytest.raises(ValidationError):
            UserListParams(page_size=101)

    def test_is_active_true(self) -> None:
        params = UserListParams(is_active=True)
        assert params.is_active is True

    def test_is_active_false(self) -> None:
        params = UserListParams(is_active=False)
        assert params.is_active is False

    def test_is_active_none_returns_all(self) -> None:
        params = UserListParams(is_active=None)
        assert params.is_active is None

    def test_serialization_round_trip(self) -> None:
        params = UserListParams(
            search="test",
            sort_by="username",
            sort_dir="asc",
            page=3,
            page_size=50,
            is_active=True,
        )
        data = params.model_dump()
        restored = UserListParams(**data)
        assert restored == params


# ---------------------------------------------------------------------------
# PermissionTemplateCreateRequest Tests
# ---------------------------------------------------------------------------


class TestPermissionTemplateCreateRequest:
    """Tests for PermissionTemplateCreateRequest validation."""

    def test_valid_full_request(self) -> None:
        req = PermissionTemplateCreateRequest(
            name="Internal SOP",
            description="Template for internal SOPs",
            document_type="SOP",
            role_permissions=[
                RoleActionMapping(role="system_admin", actions=["read", "write", "approve"]),
                RoleActionMapping(role="member", actions=["read"]),
            ],
        )
        assert req.name == "Internal SOP"
        assert req.description == "Template for internal SOPs"
        assert req.document_type == "SOP"
        assert len(req.role_permissions) == 2

    def test_name_min_length_1(self) -> None:
        req = PermissionTemplateCreateRequest(
            name="A",
            document_type="T",
            role_permissions=[RoleActionMapping(role="viewer", actions=["read"])],
        )
        assert req.name == "A"

    def test_name_empty_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PermissionTemplateCreateRequest(
                name="",
                document_type="SOP",
                role_permissions=[RoleActionMapping(role="viewer", actions=["read"])],
            )

    def test_name_max_length_200(self) -> None:
        req = PermissionTemplateCreateRequest(
            name="N" * 200,
            document_type="SOP",
            role_permissions=[RoleActionMapping(role="viewer", actions=["read"])],
        )
        assert len(req.name) == 200

    def test_name_exceeds_200_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PermissionTemplateCreateRequest(
                name="N" * 201,
                document_type="SOP",
                role_permissions=[RoleActionMapping(role="viewer", actions=["read"])],
            )

    def test_description_optional(self) -> None:
        req = PermissionTemplateCreateRequest(
            name="Template",
            document_type="SOP",
            role_permissions=[RoleActionMapping(role="viewer", actions=["read"])],
        )
        assert req.description is None

    def test_description_max_length_1000(self) -> None:
        req = PermissionTemplateCreateRequest(
            name="Template",
            description="D" * 1000,
            document_type="SOP",
            role_permissions=[RoleActionMapping(role="viewer", actions=["read"])],
        )
        assert len(req.description) == 1000

    def test_description_exceeds_1000_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PermissionTemplateCreateRequest(
                name="Template",
                description="D" * 1001,
                document_type="SOP",
                role_permissions=[RoleActionMapping(role="viewer", actions=["read"])],
            )

    def test_document_type_min_length_1(self) -> None:
        req = PermissionTemplateCreateRequest(
            name="Template",
            document_type="X",
            role_permissions=[RoleActionMapping(role="viewer", actions=["read"])],
        )
        assert req.document_type == "X"

    def test_document_type_empty_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PermissionTemplateCreateRequest(
                name="Template",
                document_type="",
                role_permissions=[RoleActionMapping(role="viewer", actions=["read"])],
            )

    def test_document_type_max_length_100(self) -> None:
        req = PermissionTemplateCreateRequest(
            name="Template",
            document_type="T" * 100,
            role_permissions=[RoleActionMapping(role="viewer", actions=["read"])],
        )
        assert len(req.document_type) == 100

    def test_document_type_exceeds_100_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PermissionTemplateCreateRequest(
                name="Template",
                document_type="T" * 101,
                role_permissions=[RoleActionMapping(role="viewer", actions=["read"])],
            )

    def test_role_permissions_min_length_1(self) -> None:
        req = PermissionTemplateCreateRequest(
            name="Template",
            document_type="SOP",
            role_permissions=[RoleActionMapping(role="viewer", actions=["read"])],
        )
        assert len(req.role_permissions) == 1

    def test_role_permissions_empty_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PermissionTemplateCreateRequest(
                name="Template",
                document_type="SOP",
                role_permissions=[],
            )

    def test_serialization_round_trip(self) -> None:
        req = PermissionTemplateCreateRequest(
            name="Test Template",
            description="A test",
            document_type="SOP",
            role_permissions=[
                RoleActionMapping(role="doc_admin", actions=["read", "write", "approve"]),
                RoleActionMapping(role="member", actions=["read"]),
            ],
        )
        data = req.model_dump()
        restored = PermissionTemplateCreateRequest(**data)
        assert restored == req

    def test_json_serialization(self) -> None:
        req = PermissionTemplateCreateRequest(
            name="Test",
            document_type="SOP",
            role_permissions=[RoleActionMapping(role="viewer", actions=["read"])],
        )
        json_str = req.model_dump_json()
        restored = PermissionTemplateCreateRequest.model_validate_json(json_str)
        assert restored == req


# ---------------------------------------------------------------------------
# PermissionTemplateUpdateRequest Tests
# ---------------------------------------------------------------------------


class TestPermissionTemplateUpdateRequest:
    """Tests for PermissionTemplateUpdateRequest validation."""

    def test_all_fields_optional(self) -> None:
        req = PermissionTemplateUpdateRequest()
        assert req.name is None
        assert req.description is None
        assert req.role_permissions is None

    def test_update_name_only(self) -> None:
        req = PermissionTemplateUpdateRequest(name="Updated Name")
        assert req.name == "Updated Name"

    def test_name_empty_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PermissionTemplateUpdateRequest(name="")

    def test_name_exceeds_200_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PermissionTemplateUpdateRequest(name="N" * 201)

    def test_description_exceeds_1000_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PermissionTemplateUpdateRequest(description="D" * 1001)

    def test_update_role_permissions(self) -> None:
        req = PermissionTemplateUpdateRequest(
            role_permissions=[RoleActionMapping(role="member", actions=["read", "write"])]
        )
        assert req.role_permissions is not None
        assert len(req.role_permissions) == 1


# ---------------------------------------------------------------------------
# RoleActionMapping Tests
# ---------------------------------------------------------------------------


class TestRoleActionMapping:
    """Tests for RoleActionMapping validation."""

    def test_valid_mapping(self) -> None:
        mapping = RoleActionMapping(role="system_admin", actions=["read", "write", "approve"])
        assert mapping.role == "system_admin"
        assert mapping.actions == ["read", "write", "approve"]

    def test_all_valid_roles(self) -> None:
        for role in ["system_admin", "doc_admin", "it_admin", "member", "viewer"]:
            mapping = RoleActionMapping(role=role, actions=["read"])  # type: ignore[arg-type]
            assert mapping.role == role

    def test_invalid_role_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RoleActionMapping(role="superuser", actions=["read"])  # type: ignore[arg-type]

    def test_all_valid_actions(self) -> None:
        for action in ["read", "write", "approve"]:
            mapping = RoleActionMapping(role="viewer", actions=[action])  # type: ignore[arg-type]
            assert action in mapping.actions

    def test_invalid_action_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RoleActionMapping(role="viewer", actions=["delete"])  # type: ignore[arg-type]

    def test_empty_actions_allowed(self) -> None:
        mapping = RoleActionMapping(role="viewer", actions=[])
        assert mapping.actions == []

    def test_multiple_actions(self) -> None:
        mapping = RoleActionMapping(role="doc_admin", actions=["read", "write", "approve"])
        assert len(mapping.actions) == 3


# ---------------------------------------------------------------------------
# AssignMembershipRequest Tests
# ---------------------------------------------------------------------------


class TestAssignMembershipRequest:
    """Tests for AssignMembershipRequest validation."""

    def test_valid_request(self) -> None:
        req = AssignMembershipRequest(user_id=1, company_id=2, role="member")
        assert req.user_id == 1
        assert req.company_id == 2
        assert req.role == "member"

    def test_all_valid_roles(self) -> None:
        for role in ["system_admin", "doc_admin", "it_admin", "member", "viewer"]:
            req = AssignMembershipRequest(user_id=1, company_id=1, role=role)  # type: ignore[arg-type]
            assert req.role == role

    def test_invalid_role_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AssignMembershipRequest(user_id=1, company_id=1, role="admin")  # type: ignore[arg-type]

    def test_missing_fields_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AssignMembershipRequest()  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# PermissionEntry Tests
# ---------------------------------------------------------------------------


class TestPermissionEntry:
    """Tests for PermissionEntry validation."""

    def test_valid_entry(self) -> None:
        entry = PermissionEntry(resource="documents", actions=["create", "read", "update"])
        assert entry.resource == "documents"
        assert entry.actions == ["create", "read", "update"]

    def test_all_valid_actions(self) -> None:
        entry = PermissionEntry(
            resource="workflows",
            actions=["create", "read", "update", "delete", "approve"],
        )
        assert len(entry.actions) == 5

    def test_invalid_action_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PermissionEntry(resource="documents", actions=["execute"])  # type: ignore[arg-type]

    def test_empty_actions_allowed(self) -> None:
        entry = PermissionEntry(resource="documents", actions=[])
        assert entry.actions == []
